#!/usr/bin/python
import glob
import os
import re
from structures import *
from string import Template
from datetime import datetime
import sys
import getopt
import logging
import ConfigParser
import time as Time
import json
import subprocess
from sift_histograms import create_histogram

from utils import config_section_map


def main(argv):
    ###############################
    # Getting program options
    ###############################
    help_str = 'eval photo'
    try:
        opts, args = getopt.getopt(argv, None, ["config=", "image-path=",
                                                "result="])
    except getopt.GetoptError as err:
        print help_str
        print str(err)
        sys.exit(2)
    for opt, arg in opts:
        if opt == '-h':
            print help_str
            sys.exit()
        elif opt in "--config":
            config_file = arg
        elif opt in "--image-path":
            image_path = arg
        elif opt in "--result":
            result = arg

    #########################
    # Chargement de la config
    #########################
    config = ConfigParser.ConfigParser()
    config.read(config_file)
    config_general = config_section_map(config, 'General')
    config_predict = config_section_map(config, 'Predict')
    config_scripts = config_section_map(config, 'Scripts')
    config_svm = config_section_map(config, 'libSvm')
    config_svm = config_section_map(config, 'libSvm')
    config_libc = config_section_map(config, 'libC')


    #########################
    # Init svm train_photos command
    #########################
    one_nn_script = config_scripts['1nn']
    svm_predict = config_svm['svm_predict']

    #########################
    # Configuration du logger
    #########################
    log_dir = config_general['log_dir']

    now = datetime.now()
    date_str = str(now.day) + '_' + str(now.hour) + '_' + str(now.minute) + "_" + str(now.second) + "_" + str(now.microsecond)
    logfile_name = os.path.basename(__file__).split('.')[0] + '-' + date_str + '.log'
    logging.basicConfig(filename=log_dir + '/' + logfile_name, level=logging.DEBUG)

    ###########################
    # Generation of sift file
    ###########################
    if not os.path.exists(image_path):
        logging.warning("not image found at path " + image_path)
        exit(1)

    working_dir = os.path.dirname(image_path)

    sift_file = os.path.join(working_dir, os.path.splitext(os.path.basename(image_path))[0] + '.sift')
    color_descriptor_exec = os.path.join(config_general['project_dir'], 'dep', 'colorDescriptor')
    create_sift_cmd = [
        color_descriptor_exec,
        '--descriptor', 'sift',
        image_path, '--output', sift_file
    ]

    logging.info('sift commande : ' + str(create_sift_cmd))
    process = subprocess.Popen(create_sift_cmd)
    while process.poll() is None:
        Time.sleep(0)
        pass
    ###########################
    # Parametrage des concepts
    ###########################
    model_folders = dict()

    folder_tmpl = Template('centers-${centers}_g-${g}_w-${w}')
    centers_tmpl = Template(os.path.join(config_predict['centers_folders'], 'centers${nb_centers}.txt'))
    model_folder_tmpl = Template(os.path.join(config_predict['sift_folders'], 'centers${nb_centers}.txt'))
    res_file = config_predict['best_results_sift']
    input_folder = config_predict['sift_folders']
    concepts = []
    with open(res_file, "r") as best_option:
        content = best_option.read().splitlines()
        for line in content:
            if 'all' in line:
                continue
            row = line.split(" ")
            concept_name = row[1]
            concepts.append(concept_name)
            concept_map = dict()
            nb_centers = row[3]
            g_value = row[5]
            w_value = row[7]
            folder_name = folder_tmpl.substitute(g=g_value, centers=nb_centers, w=w_value)
            if not input_folder.startswith("/"):
                folder_path = os.path.join(config_general['project_dir'], input_folder, folder_name)
            else:
                folder_path = os.path.join(input_folder, folder_name)
            logging.info("folder for " + concept_name + " -> " + folder_path)
            if not os.path.exists(folder_path):
                logging.warning("folder " + folder_name + " required for " + concept_name + " not found")
            else:
                concept_map['sift_folder'] = folder_path
                concept_map['sift_g'] = g_value
                concept_map['sift_w'] = w_value
                concept_map['sift_centers'] = nb_centers
                concept_map['sift_centers_file'] = centers_tmpl.substitute(nb_centers=nb_centers)
                concept_map['sift_model_file'] = os.path.join(folder_path, 'model', concept_name + ".model")
                if not os.path.exists(os.path.join(folder_path, 'model', concept_name + ".model")):
                    logging.warning("no model found : " + os.path.join(folder_path, 'model', concept_name + ".model"))
                model_folders[concept_name] = concept_map
                logging.info("map for concept : " + concept_name + " -> " + str(concept_map))
    concepts = set(concepts)

    #Parameters for fusion
    fusion_model_map = dict()
    fusion_res_files = config_predict['best_results_fusion']
    fusion_parameters = open(fusion_res_files, 'r').read().splitlines()
    for line in fusion_parameters:
        content = line.split(' ')
        concept_map = dict()
        concept_name = content[1]
        sift_coef = float(content[3])
        color_coef = float(content[5])
        concept_map['sift_coef'] = sift_coef
        concept_map['color_coef'] = color_coef
        fusion_model_map[concept_name] = concept_map

    # PArameters for color
    color_res_file = config_predict['best_results_color']
    color_input_folder = config_predict['color_folders']
    color_folder_tmpl = Template('g-${g}_w-${w}')
    color_model_folder = dict()
    with open(color_res_file, "r") as color_best_option:
        content = color_best_option.read().splitlines()
        for line in content:
            if 'all' in line:
                continue
            row = line.split(" ")
            concept_name = row[1]
            color_concept_map = dict()
            g_value = row[3]
            w_value = row[5]
            folder_name = color_folder_tmpl.substitute(g=g_value, w=w_value)
            if not input_folder.startswith("/"):
                folder_path = os.path.join(config_general['project_dir'], color_input_folder, folder_name)
            else:
                folder_path = os.path.join(color_input_folder, folder_name)
            logging.info("folder for " + concept_name + " -> " + folder_path)
            if not os.path.exists(folder_path):
                logging.warning("folder " + folder_name + " required for " + concept_name + " not found [color]")
            else:
                color_concept_map['color_folder'] = folder_path
                color_concept_map['color_g'] = g_value
                color_concept_map['color_w'] = w_value
                color_concept_map['color_model_file'] = os.path.join(folder_path, 'model', concept_name + ".model")
                if not os.path.exists(os.path.join(folder_path, 'model', concept_name + ".model")):
                    logging.warning("no model found : " + os.path.exists(os.path.join(folder_path, 'model', concept_name + ".model")))
                color_model_folder[concept_name] = color_concept_map
                logging.info("map for concept : " + concept_name + " -> " + str(concept_map))


    jpg_name = image_path
    if(os.path.splitext(image_path)[1] == '.PNG' or os.path.splitext(image_path)[1] == '.png') :
        jpg_name = os.path.splitext(image_path)[0] + '.jpg'
        print "convert"
        os.system('convert ' + image_path + ' ' + jpg_name );

    ####################################################"
    # Color histogrammes
    #####################################################
    lib = cdll.LoadLibrary(config_libc['libhistogram'])
    libc = CDLL('libc.so.6')
    fp = libc.fopen(os.path.join(working_dir, "color_histogram.svm"), "w")
    hist = pointer(HISTROGRAM())
    path = jpg_name
    lib.read_img(hist,  path)
    lib.print_histogram_libsvm(fp, hist, 0)
    lib.free_histogram(hist)
    libc.fflush(fp) # need to fflush otherwise data won't be writed till the prg finished :'(
    libc.close(fp)

    if(os.path.splitext(image_path)[1] == '.PNG' or os.path.splitext(image_path)[1] == '.png') :
        os.system('rm ' + jpg_name);

    ####################################################"
    # Predict Color
    ######################################################"
    res_files = []
    for concept in color_model_folder:
        concept_map = color_model_folder[concept]
        g_param = concept_map['color_g']
        w_param = concept_map['color_w']
        svm_file = os.path.join(working_dir, 'color_histogram.svm')
        logging.info('color svm file for predict ' + svm_file)
        logging.info('model for predict ' + concept_map['color_model_file'])
        concept_out = os.path.join(working_dir, concept + '.color.out')
        res_files.append(concept_out )
        logging.info("best parameters for " + concept + " concept ->  " +
                     " g : " + g_param +
                     " w : " + w_param)
        predict_command = [
            svm_predict,
            '-b', '1',
            svm_file,
            concept_map['color_model_file'],
            concept_out
        ]
        logging.info("predict color cmd : " + " ".join(predict_command))
        predict_process = subprocess.Popen(predict_command)
        while predict_process.poll() is None:
            Time.sleep(0)
            pass
        p_rc = predict_process.returncode
        if p_rc != 0:
            logging.warning("error during prediction for concept " + concept)
            logging.warning("command : " + " ".join(predict_command))
            exit(1)

    collect_dict = dict()
    fusion_collect_dict = dict()
    for res in res_files:
        cpt_name = os.path.basename(res.split('.')[0])
        if not cpt_name in fusion_collect_dict:
            fusion_collect_dict[cpt_name] = 0.0
        if not os.path.exists(res):
            logging.warning("no output res for " + res)
            continue
        with open(res, "r") as results_stream:
            content = results_stream.read().splitlines()
            is_concept = content[1].split(" ")[0]
            if content[0].split(" ")[1] == "1":
                res_map = content[1].split(" ")[1]
            else:
                res_map = content[1].split(" ")[2]
            fusion_collect_dict[cpt_name] = float(res_map) * float(fusion_model_map[cpt_name]['color_coef']) # calcul of fusion on the thumb
            collect_dict[cpt_name] = {
                "map" : res_map,
                "is_concept" : is_concept,
                "concept" : cpt_name
            }

    finale_res = os.path.basename(image_path) + ".color.json"
    finale_res_path = os.path.join(working_dir, finale_res)
    with open(finale_res_path, "w") as final_res_stream:
        final_res_stream.write(json.dumps(collect_dict))

    while process.poll() is None:
        Time.sleep(0)
        pass

    rc = process.returncode
    if rc != 0:
        logging.warning("error while generating sift file")
        exit(1)

    if not os.path.exists(sift_file):
        logging.warning('error while creating sift file')
        exit(1)


    ###########################
    # Generation of mapping
    ###########################
    temp_sift_file = os.path.join(working_dir, sift_file + '.tmp')
    os.system("sed -n '4,$p' " + sift_file + " | tr -d \";\" |sed 's/<CIRCLE [1-9].*> //' > " + temp_sift_file)
    map_files = []
    for concept in concepts:
        if concept_name not in model_folders:
            logging.info("missing concept " + concept_name + " into information map")
            continue
        with open(one_nn_script, "r") as file_string:
            concept_map = model_folders[concept]
            mapping_file = os.path.join(working_dir, "mapping-center" + str(concept_map['sift_centers']) + ".map")
            logging.info("mapping at " + mapping_file)
            map_files.append(mapping_file)  # on stock les chemin vers les fichiers pour les histogrammes
            if not os.path.exists(mapping_file):
                command = []
                command += ["R", "--slave", "--no-save", "--no-restore", "--no-environ", "--args"]
                command += [concept_map['sift_centers_file'],
                            str(concept_map['sift_centers']),
                            temp_sift_file,
                            mapping_file]
                logging.info("mapping command for concept " + concept + " -> " + " ".join(command))
                mapping_process = subprocess.Popen(command,
                                                   stdout=subprocess.PIPE,
                                                   stderr=subprocess.PIPE,
                                                   stdin=file_string)
            while mapping_process.poll() is None:
                Time.sleep(0)
                pass

    map_files = set(map_files)
    generated_mapping_files = glob.glob(working_dir + '/*.map')
    for gen_file in set(generated_mapping_files):
        if gen_file not in map_files:
            logging.warning("failed to create mapping for file " + gen_file)
        nb_cluster = re.search('([0-9]*).map$', gen_file).group(1)
        result_files_svm_path = os.path.join(working_dir, "svm_file" + nb_cluster + ".svm")
        try:
            svm_file = open(result_files_svm_path, "w")
            logging.info("opening : " + result_files_svm_path)
            nb_cluster_int = int(nb_cluster)
            histogram = create_histogram(gen_file, nb_cluster_int)
            svm_file.write("0 ")
            for i, val in enumerate(histogram):
                if val != 0.0:
                    svm_file.write(str(i+1) + ":")
                    svm_file.write(str(val) + " ")
            svm_file.write("\n")
            svm_file.close()
        except ValueError:
            logging.warning("error in map file, cannot convert " + nb_cluster + " to int")

    res_files = []
    for concept in model_folders:
        concept_map = model_folders[concept]
        g_param = concept_map['sift_g']
        w_param = concept_map['sift_w']
        nb_centers = concept_map['sift_centers']
        svm_file = os.path.join(working_dir, 'svm_file' + nb_centers + ".svm")
        logging.info('svm file for predict ' + svm_file)
        logging.info('model for predict ' + concept_map['sift_model_file'])
        concept_out = os.path.join(working_dir, concept + '.sift.out')
        res_files.append(concept_out )
        logging.info("best parameters for " + concept + " concept ->  " +
                     "centers " + nb_centers +
                     " g : " + g_param +
                     " w : " + w_param)
        predict_command = [
            svm_predict,
            '-b', '1',
            svm_file,
            concept_map['sift_model_file'],
            concept_out
        ]
        logging.info(" ".join(predict_command))
        predict_process = subprocess.Popen(predict_command)

        while predict_process.poll() is None:
            Time.sleep(0)
            pass
        p_rc = predict_process.returncode
        if p_rc != 0:
            logging.warning("error during prediction for concept " + concept)
            logging.warning("command : " + " ".join(predict_command))
            exit(1)

    collect_dict = dict()
    for res in res_files:
        cpt_name = os.path.basename(res.split('.')[0])
        if not os.path.exists(res):
            logging.warning("no output res for " + res)
            continue
        with open(res, "r") as results_stream:
            content = results_stream.read().splitlines()
            is_concept = content[1].split(" ")[0]
            if content[0].split(" ")[1] == "1":
                res_map = content[1].split(" ")[1]
            else:
                res_map = content[1].split(" ")[2]
            fusion_collect_dict[cpt_name] += float(res_map) * float(fusion_model_map[cpt_name]['sift_coef']) # calcul of fusion on the thumb
            collect_dict[cpt_name] = {
                "map" : res_map,
                "is_concept" : is_concept,
                "concept" : cpt_name
            }

    finale_res = os.path.basename(image_path) + ".sift.json"
    finale_res_path = os.path.join(working_dir, finale_res)
    with open(finale_res_path, "w") as final_res_stream:
        final_res_stream.write(json.dumps(collect_dict))

    fusion_json_dict = dict()
    for concept in fusion_collect_dict:
        fusion_json_dict[concept] = dict()
        fusion_json_dict[concept]['is_concept'] = 1 if fusion_collect_dict[concept] > 0.5 else  -1
        fusion_json_dict[concept]['concept'] = concept
        fusion_json_dict[concept]['map'] = fusion_collect_dict[concept]

    finale_res = os.path.basename(image_path) + ".fusion.json"
    finale_res_path = os.path.join(working_dir, finale_res)
    with open(finale_res_path, "w") as final_res_stream:
        final_res_stream.write(json.dumps(fusion_json_dict))



if __name__ == "__main__":
    main(sys.argv[1:])
